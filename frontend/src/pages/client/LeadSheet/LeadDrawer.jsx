import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import clientApi from '../../../api/client';
import { leadInitials, friendlyOutcome } from './leadUtils';
import './LeadDrawer.css';

const OUTCOME_BADGE = {
  Interested: 'success',
  Not_Interested: 'danger',
  Callback_Requested: 'warning',
  Busy: 'warning',
};

const fmtDuration = (s) => {
  if (s == null || s < 0) return '—';
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
};

const fmtAudioTime = (t) => {
  if (!Number.isFinite(t)) return '0:00';
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
};

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

const computeAnalytics = (transcript, durationSeconds) => {
  if (!Array.isArray(transcript) || transcript.length === 0) {
    return { aiRatio: 0, custRatio: 0, turns: 0, aiTurns: 0, custTurns: 0, avgResponse: 0 };
  }
  let aiWords = 0;
  let custWords = 0;
  let aiTurns = 0;
  let custTurns = 0;
  transcript.forEach((t) => {
    const text = t.content || t.text || '';
    const w = text.split(/\s+/).filter(Boolean).length;
    if (t.role === 'assistant' || t.role === 'bot') {
      aiWords += w;
      aiTurns += 1;
    } else {
      custWords += w;
      custTurns += 1;
    }
  });
  const totalWords = aiWords + custWords || 1;
  const totalTurns = aiTurns + custTurns;
  const avgResponse = totalTurns > 0
    ? Math.round(((durationSeconds || 0) / totalTurns) * 10) / 10
    : 0;
  return {
    aiRatio: Math.round((aiWords / totalWords) * 100),
    custRatio: Math.round((custWords / totalWords) * 100),
    turns: totalTurns,
    aiTurns,
    custTurns,
    avgResponse,
  };
};

const LeadDrawer = ({ open, lead, onClose }) => {
  const [activeTab, setActiveTab] = useState('analytics');
  const [callData, setCallData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [transcriptSearch, setTranscriptSearch] = useState('');
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioProgress, setAudioProgress] = useState(0);
  const [audioDuration, setAudioDuration] = useState(0);
  const [speedMenuOpen, setSpeedMenuOpen] = useState(false);
  const audioRef = useRef(null);

  const sessionCallId = lead?.sessionCallId || lead?.session_call_id || null;

  const fetchCallDetails = useCallback(async (showSpinner = true) => {
    const lookupId = sessionCallId || lead?.id;
    if (!lookupId) {
      setCallData(null);
      setPolling(false);
      return;
    }
    if (showSpinner) setLoading(true);
    try {
      const res = await clientApi.get(`/api/calls/${lookupId}`);
      const call = res.data;
      if (!call?.session_call_id) {
        setCallData(null);
        setPolling(false);
        return;
      }
      call.transcript = parseJsonField(call.transcript, []);
      if (!Array.isArray(call.transcript)) call.transcript = [];
      call.extraction_json = parseJsonField(call.extraction_json, null);
      setCallData(call);
      setPolling(call.in_progress === true || lead?.status === 'calling');
    } catch {
      setCallData(null);
      setPolling(lead?.status === 'calling');
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [sessionCallId, lead?.id, lead?.status]);

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
        const message = await parseBlobError(err);
        setRecordingError(message);
      }
    } finally {
      setRecordingLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !lead) return;
    setActiveTab('analytics');
    setTranscriptSearch('');
    fetchCallDetails(true);
  }, [open, lead, fetchCallDetails]);

  useEffect(() => {
    if (!open) {
      setCallData(null);
      setPolling(false);
      setRecordingUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      setRecordingError(null);
      setIsPlaying(false);
      setAudioProgress(0);
    }
  }, [open]);

  useEffect(() => {
    if (!polling || !open) return undefined;
    const interval = setInterval(() => fetchCallDetails(false), 2000);
    return () => clearInterval(interval);
  }, [polling, open, fetchCallDetails]);

  useEffect(() => {
    if (!open || !callData?.session_call_id) return;
    fetchRecording(callData.session_call_id, callData.in_progress);
  }, [open, callData?.session_call_id, callData?.in_progress, fetchRecording]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    if (!open) return undefined;
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const stats = useMemo(
    () => computeAnalytics(callData?.transcript, callData?.duration_seconds),
    [callData?.transcript, callData?.duration_seconds],
  );

  const outcome = callData?.outcome || lead?.outcome || '';
  const badgeTone = OUTCOME_BADGE[outcome] || 'neutral';
  const phone = callData?.phone || lead?.phone || '';
  const displayName = lead?.name || callData?.name || 'Unknown lead';

  const extractionEntries = callData?.extraction_json
    ? Object.entries(callData.extraction_json).filter(([, v]) => v != null && v !== '')
    : [];

  const topicKeys = extractionEntries
    .map(([k]) => k.replace(/_/g, ' '))
    .filter((k) => !['intent', 'project', 'builder', 'interest', 'timeline'].includes(k.toLowerCase()));

  const filteredTranscript = (callData?.transcript || []).filter((t) => {
    const text = (t.content || t.text || '').toLowerCase();
    return !transcriptSearch || text.includes(transcriptSearch.toLowerCase());
  });

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
    }
  };

  const skipTime = (amt) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = Math.max(
      0,
      Math.min(audioDuration, audioRef.current.currentTime + amt),
    );
  };

  const changeSpeed = (sp) => {
    if (audioRef.current) audioRef.current.playbackRate = sp;
    setPlaybackSpeed(sp);
    setSpeedMenuOpen(false);
  };

  const seekTo = (clientX, rect) => {
    if (!audioRef.current || !audioDuration) return;
    const t = Math.max(0, Math.min(audioDuration, ((clientX - rect.left) / rect.width) * audioDuration));
    audioRef.current.currentTime = t;
    setAudioProgress(t);
  };

  const waveHeights = useMemo(
    () => Array.from({ length: 88 }, (_, i) => (
      Math.abs(Math.sin(i * 0.41) * 14) + Math.abs(Math.cos(i * 0.29) * 7) + 5
    )),
    [],
  );

  useEffect(() => {
    if (!speedMenuOpen) return undefined;
    const close = () => setSpeedMenuOpen(false);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [speedMenuOpen]);

  const callTimestamp = callData?.created_at || lead?.lastCalledAt || lead?.updatedAt;

  if (!lead) return null;

  return (
    <>
      {open && (
        <button type="button" className="ls-drawer__backdrop" onClick={onClose} aria-label="Close drawer" />
      )}
      <aside className={`ls-drawer ${open ? 'ls-drawer--open' : ''}`} aria-hidden={!open}>
        <header className="ls-drawer__header">
          <div className="ls-drawer__header-top">
            <div className="ls-drawer__identity">
              <div className="ls-drawer__avatar">{leadInitials(displayName)}</div>
              <div>
                <div className="ls-drawer__name-row">
                  <span className="ls-drawer__name">{displayName}</span>
                  {outcome && (
                    <span className={`ls-drawer__badge ls-drawer__badge--${badgeTone}`}>
                      {friendlyOutcome(outcome).toUpperCase()}
                    </span>
                  )}
                </div>
                <div className="ls-drawer__meta">
                  {phone && (
                    <>
                      <span className="material-symbols-outlined">call</span>
                      <span className="ls-drawer__meta-phone">{phone}</span>
                      <span>·</span>
                    </>
                  )}
                  <span>
                    {callTimestamp
                      ? new Date(callTimestamp).toLocaleString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—'}
                  </span>
                </div>
              </div>
            </div>
            <div className="ls-drawer__header-actions">
              <button type="button" className="ls-drawer__icon-btn" onClick={onClose} aria-label="Close">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
          </div>

          <nav className="ls-drawer__tabs" aria-label="Call details">
            {[
              { id: 'overview', label: 'Overview' },
              { id: 'details', label: 'Details' },
              { id: 'transcript', label: 'Transcript' },
              { id: 'recording', label: 'Recording' },
              { id: 'ai', label: 'AI Summary' },
              { id: 'timeline', label: 'Call Timeline' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`ls-drawer__tab ${activeTab === tab.id ? 'ls-drawer__tab--active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </header>

        <div className="ls-drawer__body">
          {loading ? (
            <div className="ls-drawer__loading">
              <div className="ls-drawer__spinner" />
              <span>Loading call data…</span>
            </div>
          ) : !callData ? (
            <div className="ls-drawer__empty-state">
              {lead.status === 'calling'
                ? 'Call in progress — details will appear shortly.'
                : 'No call data available for this lead yet.'}
            </div>
          ) : (
            <>
              {activeTab === 'overview' && (
                <div className="ls-drawer__panel">
                  <div className="ls-drawer__card">
                    <div className="ls-drawer__card-head">
                      <div className="ls-drawer__card-title">
                        <span>Overview</span>
                      </div>
                      <span className="ls-drawer__card-sub">{stats.turns || 0} total turns</span>
                    </div>
                    <div className="ls-drawer__overview-grid">
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Status</div>
                        <div className="ls-drawer__overview-value">{lead.status || '—'}</div>
                      </div>
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Outcome</div>
                        <div className="ls-drawer__overview-value">{friendlyOutcome(callData?.outcome || lead?.outcome || '') || '—'}</div>
                      </div>
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Attempts</div>
                        <div className="ls-drawer__overview-value">{lead.attempts ?? 0}</div>
                      </div>
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Duration</div>
                        <div className="ls-drawer__overview-value">{fmtDuration(callData?.duration_seconds ?? lead?.lastCallDurationSeconds)}</div>
                      </div>
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Credits</div>
                        <div className="ls-drawer__overview-value">{callData?.credits_used ?? '—'}</div>
                      </div>
                      <div className="ls-drawer__overview-item">
                        <div className="ls-drawer__overview-label">Campaign</div>
                        <div className="ls-drawer__overview-value">{lead.campaignName || '—'}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'details' && (
                <div className="ls-drawer__panel">
                  {extractionEntries.length > 0 ? (
                    <>
                      <div className="ls-drawer__section-label">
                        <span className="material-symbols-outlined">data_object</span>
                        <span>Extracted Info</span>
                      </div>
                      <div className="ls-drawer__extract-grid">
                        {extractionEntries.map(([key, val]) => (
                          <div key={key} className="ls-drawer__extract-cell">
                            <div className="ls-drawer__extract-key">{key.replace(/_/g, ' ')}</div>
                            <div className={`ls-drawer__extract-val ${key.toLowerCase() === 'intent' ? 'ls-drawer__extract-val--intent' : ''}`}>
                              {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                            </div>
                          </div>
                        ))}
                      </div>
                      {topicKeys.length > 0 && (
                        <>
                          <div className="ls-drawer__section-label">Key Topics</div>
                          <div className="ls-drawer__topics">
                            {topicKeys.map((topic) => (
                              <span key={topic} className="ls-drawer__topic">{topic}</span>
                            ))}
                          </div>
                        </>
                      )}
                    </>
                  ) : (
                    <div className="ls-drawer__empty-state">No extracted data for this call.</div>
                  )}
                </div>
              )}

              {activeTab === 'transcript' && (
                <div className="ls-drawer__panel">
                  <div className="ls-drawer__search">
                    <span className="material-symbols-outlined">search</span>
                    <input
                      type="search"
                      placeholder="Search in transcript…"
                      value={transcriptSearch}
                      onChange={(e) => setTranscriptSearch(e.target.value)}
                    />
                  </div>
                  <div className="ls-drawer__transcript">
                    {filteredTranscript.length > 0 ? (
                      filteredTranscript.map((turn, i) => {
                        const isAi = turn.role === 'assistant' || turn.role === 'bot';
                        const text = turn.content || turn.text || '';
                        return (
                          <div
                            key={`${i}-${text.slice(0, 20)}`}
                            className={`ls-drawer__turn ${isAi ? '' : 'ls-drawer__turn--user'}`}
                          >
                            <div className="ls-drawer__turn-head">
                              <div className={`ls-drawer__turn-avatar ${isAi ? 'ls-drawer__turn-avatar--ai' : 'ls-drawer__turn-avatar--user'}`}>
                                <span className="material-symbols-outlined">
                                  {isAi ? 'smart_toy' : 'person'}
                                </span>
                              </div>
                              <span className="ls-drawer__turn-role">{isAi ? 'AI Agent' : 'Customer'}</span>
                              {turn.timestamp != null && (
                                <span className="ls-drawer__turn-time">{fmtAudioTime(turn.timestamp)}</span>
                              )}
                            </div>
                            <div className={`ls-drawer__bubble ${isAi ? 'ls-drawer__bubble--ai' : 'ls-drawer__bubble--user'}`}>
                              {text}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="ls-drawer__empty-state">
                        {transcriptSearch ? 'No matching messages.' : 'No transcript available.'}
                      </div>
                    )}
                    {callData.in_progress && (
                      <div className="ls-drawer__typing">
                        <div className="ls-drawer__turn-avatar ls-drawer__turn-avatar--ai">
                          <span className="material-symbols-outlined">smart_toy</span>
                        </div>
                        <div className="ls-drawer__typing-dots">
                          <span />
                          <span />
                          <span />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'recording' && (
                <div className="ls-drawer__panel">
                  {recordingLoading ? (
                    <div className="ls-drawer__player-loading">
                      <div className="ls-drawer__player-spinner" />
                      <span>Loading audio…</span>
                    </div>
                  ) : recordingUrl ? (
                    <div className="ls-drawer__panel-recording">
                      <audio
                        ref={audioRef}
                        className="ls-drawer__audio"
                        src={recordingUrl || undefined}
                        onTimeUpdate={() => setAudioProgress(audioRef.current?.currentTime || 0)}
                        onLoadedMetadata={() => setAudioDuration(audioRef.current?.duration || 0)}
                        onPlay={() => setIsPlaying(true)}
                        onPause={() => setIsPlaying(false)}
                        onEnded={() => setIsPlaying(false)}
                      />
                      <div className="ls-drawer__player-row">
                        <button type="button" className="ls-drawer__player-btn ls-drawer__player-btn--play" onClick={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'}>
                          <span className="material-symbols-outlined">{isPlaying ? 'pause' : 'play_arrow'}</span>
                        </button>
                        <div className="ls-drawer__waveform" role="slider" tabIndex={0} aria-label="Seek" aria-valuemin={0} aria-valuemax={audioDuration} aria-valuenow={audioProgress} onClick={(e) => seekTo(e.clientX, e.currentTarget.getBoundingClientRect())}>
                          {waveHeights.map((h, i) => {
                            const active = audioDuration > 0 && (audioProgress / audioDuration) > (i / waveHeights.length);
                            return (
                              <div key={i} className={`ls-drawer__wave-bar ${active ? 'ls-drawer__wave-bar--active' : ''}`} style={{ height: `${h}px` }} />
                            );
                          })}
                        </div>
                        <div className="ls-drawer__player-utils">
                          <div className="ls-drawer__speed-wrap">
                            <button type="button" className="ls-drawer__speed-btn" onClick={(e) => { e.stopPropagation(); setSpeedMenuOpen((v) => !v); }}>
                              {playbackSpeed}x
                              <span className="material-symbols-outlined">expand_more</span>
                            </button>
                            {speedMenuOpen && (
                              <div className="ls-drawer__speed-menu" onClick={(e) => e.stopPropagation()}>
                                {[0.75, 1, 1.25, 1.5, 2].map((sp) => (
                                  <button key={sp} type="button" className={`ls-drawer__speed-option ${playbackSpeed === sp ? 'ls-drawer__speed-option--active' : ''}`} onClick={() => changeSpeed(sp)}>
                                    {sp}x
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                          <a href={recordingUrl} download={`call_${phone || 'recording'}.mp3`} className="ls-drawer__download" aria-label="Download recording">
                            <span className="material-symbols-outlined">download</span>
                          </a>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="ls-drawer__player-empty">
                      <span className="material-symbols-outlined">mic_off</span>
                      <span>
                        {recordingError || (callData?.in_progress ? 'Recording available after call ends.' : 'No recording available.')}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        <footer className="ls-drawer__player" />
      </aside>
    </>
  );
};

export default LeadDrawer;
