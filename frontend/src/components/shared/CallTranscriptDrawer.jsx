import { useState, useEffect, useRef, useCallback } from 'react';
import clientApi from '../../api/client';

const CallTranscriptDrawer = ({ isOpen, sessionCallId, onClose, leadName }) => {
  const [callData, setCallData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);
  const drawerRef = useRef(null);

  // Load call transcript details
  const fetchCallDetails = useCallback(async (showSpinner = true) => {
    if (!sessionCallId) return;
    if (showSpinner) setLoading(true);
    
    try {
      const response = await clientApi.get(`/api/calls/${sessionCallId}`);
      if (response.data && response.data.session_call_id) {
        const call = response.data;
        // Defensive: parse JSONB fields if backend returned them as strings
        if (typeof call.transcript === 'string') {
          try { call.transcript = JSON.parse(call.transcript); } catch { call.transcript = []; }
        }
        if (typeof call.extraction_json === 'string') {
          try { call.extraction_json = JSON.parse(call.extraction_json); } catch { call.extraction_json = null; }
        }
        setCallData(call);
        setIsPolling(call.in_progress === true);
      }
    } catch (err) {
      console.warn('API error fetching call details', err);
      setCallData(null);
      setIsPolling(false);
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, [sessionCallId]);

  useEffect(() => {
    let timer;
    if (isOpen && sessionCallId) {
      timer = setTimeout(() => {
        fetchCallDetails(true);
      }, 0);
    } else {
      timer = setTimeout(() => {
        setCallData(null);
        setIsPolling(false);
      }, 0);
    }
    return () => clearTimeout(timer);
  }, [isOpen, sessionCallId, fetchCallDetails]);

  // Live polling for in-progress transcripts (polls every 3 seconds)
  useEffect(() => {
    if (!isPolling || !isOpen || !sessionCallId) return;

    const interval = setInterval(() => {
      fetchCallDetails(false);
    }, 2000);

    return () => clearInterval(interval);
  }, [isPolling, isOpen, sessionCallId, fetchCallDetails]);

  const fetchRecording = useCallback(async (resolvedSessionCallId, inProgress) => {
    if (!resolvedSessionCallId) return;
    setRecordingLoading(true);
    setRecordingError(null);
    try {
      const recResp = await clientApi.get(
        `/api/calls/${resolvedSessionCallId}/recording/play`,
        { responseType: 'blob' }
      );
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
        setRecordingError(err.response?.data?.detail || 'No recording available');
      }
    } finally {
      setRecordingLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen || !callData?.session_call_id) return;
    fetchRecording(callData.session_call_id, callData.in_progress);
  }, [isOpen, callData?.session_call_id, callData?.recording_url, callData?.in_progress, fetchRecording]);

  useEffect(() => {
    if (isOpen) return;
    setRecordingUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setRecordingError(null);
    setRecordingLoading(false);
  }, [isOpen]);

  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  };

  const parseHangupJson = (raw) => {
    if (!raw) return {};
    if (typeof raw === 'object') return raw;
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  };

  const hangupSourceLabel = (source) => {
    const s = (source || '').toString().trim().toLowerCase();
    if (s === 'callee') return 'Callee hung up';
    if (s === 'caller') return 'Caller hung up';
    if (s === 'api' || s === 'api request') return 'API hangup';
    return source || 'Unknown';
  };

  const outcomeLabel = (outcome) => {
    const labels = {
      Interested: 'Connected',
      Not_Interested: 'Not Interested',
      Early_Disconnect: 'Hung up early',
      Callback_Requested: 'Callback requested',
      No_Answer: 'No answer',
      Busy: 'Busy',
      Unknown: 'Could not determine',
    };
    const key = (outcome || '').toString().trim();
    return labels[key] || key.replace(/_/g, ' ') || 'Unknown';
  };

  const getInitials = (name) => {
    if (!name) return 'LD';
    return name
      .split(' ')
      .map(part => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
  };

  if (!isOpen) return null;

  return (
    <div 
      ref={drawerRef}
      className="fixed right-0 top-0 bottom-0 w-full sm:w-[480px] bg-arctic-surface dark:bg-molten-surface shadow-2xl flex flex-col border-l border-outline-variant dark:border-[#2A345E] transition-all transform animate-slide-in-right z-50"
      id="drawerContent"
    >
        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-primary">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            <p className="mt-2 text-sm text-arctic-text-muted">Loading transcript...</p>
          </div>
        ) : callData ? (
          <>
            {/* Drawer Header */}
            <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-start bg-surface dark:bg-molten-surface shrink-0">
              <div>
                <div className="flex items-center gap-3 mb-1">
                  <h2 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">
                    {leadName || 'Call Record'}
                  </h2>
                  <span className={`inline-flex items-center gap-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    callData.in_progress
                      ? 'bg-secondary-container/20 text-on-secondary-container dark:text-secondary-fixed'
                      : 'bg-surface-variant text-on-surface-variant dark:text-molten-text-muted'
                  }`}>
                    {callData.in_progress ? (
                      <>
                        <svg className="w-5 h-3" viewBox="0 0 24 16">
                          <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0s' }} width="2" x="0" y="2"></rect>
                          <rect className="waveform-bar" height="16" rx="1" style={{ animationDelay: '0.2s' }} width="2" x="4" y="0"></rect>
                          <rect className="waveform-bar" height="10" rx="1" style={{ animationDelay: '0.4s' }} width="2" x="8" y="3"></rect>
                          <rect className="waveform-bar" height="14" rx="1" style={{ animationDelay: '0.1s' }} width="2" x="12" y="1"></rect>
                          <rect className="waveform-bar" height="8" rx="1" style={{ animationDelay: '0.3s' }} width="2" x="16" y="4"></rect>
                          <rect className="waveform-bar" height="12" rx="1" style={{ animationDelay: '0.15s' }} width="2" x="20" y="2"></rect>
                        </svg>
                        Connected
                      </>
                    ) : (
                      'Completed'
                    )}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-sm text-on-surface-variant dark:text-molten-text-muted tabular-nums">
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[16px]">phone</span> {callData.phone}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[16px]">schedule</span> {formatDuration(callData.duration_seconds)}
                  </span>
                </div>
              </div>
              <button 
                onClick={onClose} 
                className="p-2 text-on-surface-variant hover:bg-surface-variant rounded-full transition-colors cursor-pointer"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {/* Post-call summary strip */}
            {!callData.in_progress && (
              <div className="px-6 py-3 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-low dark:bg-molten-bg/60 shrink-0">
                <div className="flex flex-wrap gap-3 text-xs text-on-surface-variant dark:text-molten-text-muted">
                  <span className="inline-flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">timer</span>
                    {formatDuration(callData.duration_seconds)}
                  </span>
                  {callData.plivo_hangup_json && (
                    <span className="inline-flex items-center gap-1">
                      <span className="material-symbols-outlined text-[14px]">call_end</span>
                      {hangupSourceLabel(parseHangupJson(callData.plivo_hangup_json).hangup_source)}
                    </span>
                  )}
                  {(callData.outcome || callData.extraction_json?.intent_status) && (
                    <span className="inline-flex items-center gap-1">
                      <span className="material-symbols-outlined text-[14px]">label</span>
                      {outcomeLabel(callData.outcome || callData.extraction_json?.intent_status)}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Transcript Conversation Area */}
            <div className="flex-1 overflow-y-auto p-6 bg-arctic-bg dark:bg-molten-bg/40 flex flex-col gap-6" id="chatArea">
              {Array.isArray(callData.transcript) && callData.transcript.length > 0 ? (
                callData.transcript.map((turn, index) => {
                  const isAi = turn.role === 'assistant' || turn.role === 'bot';
                  return isAi ? (
                    /* AI Bubble */
                    <div 
                      key={index} 
                      className="flex gap-3 max-w-[85%] opacity-0 transform -translate-x-4"
                      style={{ animation: `bubble-left 0.4s ease-out ${Math.min(index * 0.1, 0.4)}s forwards` }}
                    >
                      <div className="w-8 h-8 rounded-full bg-primary-container dark:bg-molten-primary/10 text-primary dark:text-molten-primary flex items-center justify-center shrink-0 mt-1">
                        <span className="material-symbols-outlined text-sm">robot_2</span>
                      </div>
                      <div className="bg-surface dark:bg-molten-surface border-l-2 border-primary dark:border-molten-primary rounded-r-xl rounded-bl-xl p-3 shadow-sm text-sm text-on-surface dark:text-molten-text">
                        {turn.content}
                      </div>
                    </div>
                  ) : (
                    /* Human Bubble */
                    <div 
                      key={index} 
                      className="flex gap-3 max-w-[85%] self-end opacity-0 transform translate-x-4"
                      style={{ animation: `bubble-right 0.4s ease-out ${Math.min(index * 0.1, 0.4)}s forwards` }}
                    >
                      <div className="bg-primary dark:bg-molten-primary text-on-primary dark:text-molten-bg rounded-l-xl rounded-br-xl p-3 shadow-sm inner-shadow-top text-sm">
                        {turn.content}
                      </div>
                      <div className="w-8 h-8 rounded-full bg-surface-variant dark:bg-molten-surface border border-outline-variant dark:border-transparent text-on-surface-variant dark:text-molten-text flex items-center justify-center shrink-0 mt-1 font-bold text-xs">
                        {getInitials(leadName)}
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="flex-1 flex items-center justify-center text-arctic-text-muted dark:text-molten-text-muted font-label-md">
                  No transcript details captured yet.
                </div>
              )}

              {/* In Progress Typing Indicator */}
              {callData.in_progress && (
                <div className="flex gap-3 max-w-[85%] opacity-0 transform -translate-x-4" style={{ animation: 'bubble-left 0.4s ease-out 0.4s forwards' }}>
                  <div className="w-8 h-8 rounded-full bg-primary-container dark:bg-molten-primary/10 text-primary dark:text-molten-primary flex items-center justify-center shrink-0 mt-1">
                    <span className="material-symbols-outlined text-sm">robot_2</span>
                  </div>
                  <div className="bg-surface dark:bg-molten-surface border-l-2 border-primary dark:border-molten-primary rounded-r-xl rounded-bl-xl px-4 py-3 shadow-sm flex items-center gap-1 h-[44px]">
                    <div className="w-1.5 h-1.5 bg-outline rounded-full typing-dot"></div>
                    <div className="w-1.5 h-1.5 bg-outline rounded-full typing-dot"></div>
                    <div className="w-1.5 h-1.5 bg-outline rounded-full typing-dot"></div>
                  </div>
                </div>
              )}

              {/* Extracted Insights Card */}
              {callData.extraction_json && Object.keys(callData.extraction_json).length > 0 && (
                <div className="mt-4 bg-surface dark:bg-molten-surface rounded-lg border border-outline-variant dark:border-[#2A345E] p-4 shadow-sm animate-fade-in-up">
                  <div className="flex items-center gap-2 mb-3 border-b border-outline-variant dark:border-[#2A345E] pb-2">
                    <span className="material-symbols-outlined text-primary dark:text-molten-primary text-sm">auto_awesome</span>
                    <h4 className="font-label-sm text-label-sm font-bold text-on-surface dark:text-molten-text">Extracted Insights</h4>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    {Object.entries(callData.extraction_json).map(([key, val]) => (
                      <div key={key} className={key === 'Suggested Action' ? 'col-span-2' : ''}>
                        <span className="block text-xs text-on-surface-variant dark:text-molten-text-muted mb-1">{key}</span>
                        <span className={`text-sm ${
                          key === 'Interest Level' 
                            ? 'inline-flex items-center px-2 py-0.5 rounded bg-secondary-container/20 text-secondary font-medium'
                            : 'text-on-surface dark:text-molten-text'
                        }`}>
                          {String(val)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Call Recording */}
            <div className="p-4 border-t border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-molten-surface shrink-0">
              {recordingLoading ? (
                <div className="flex justify-center items-center gap-2 text-sm text-arctic-text-muted dark:text-molten-text-muted py-2">
                  <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                  Loading audio...
                </div>
              ) : recordingUrl ? (
                <div className="flex items-center gap-2">
                  <audio controls src={recordingUrl} className="flex-1 h-10 outline-none" controlsList="nodownload" />
                  <a 
                    href={recordingUrl} 
                    download={`call_recording_${callData.phone || 'lead'}.mp3`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center w-10 h-10 shrink-0 bg-surface-variant dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface-variant dark:text-molten-text-muted hover:bg-outline-variant dark:hover:bg-[#2A345E]/50 transition-colors cursor-pointer group"
                    title="Download Recording"
                  >
                    <span className="material-symbols-outlined text-lg group-hover:text-primary dark:group-hover:text-molten-primary transition-colors">download</span>
                  </a>
                </div>
              ) : (
                <div className="text-center text-xs text-arctic-text-muted dark:text-molten-text-muted">
                  {recordingError || (callData.in_progress
                    ? 'Recording will be available after the call completes.'
                    : 'No recording available for this call.')}
                </div>
              )}
            </div>

            {/* Drawer Footer Actions */}
            <div className="p-4 border-t border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-molten-surface shrink-0 flex gap-3">
              {/* TODO: Drawer buttons "Pause Campaign" and "Schedule Follow-up" are unsupported in client call drawer in Phase 1
              <button 
                onClick={onClose}
                className="flex-1 bg-surface-variant dark:bg-slate-800 text-on-surface dark:text-molten-text py-2 rounded-lg font-label-md text-label-md hover:bg-outline-variant transition-colors cursor-pointer"
              >
                Pause Campaign
              </button>
              <button className="flex-1 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg py-2 rounded-lg font-label-md text-label-md shadow-sm inner-shadow-top hover:brightness-110 transition-colors cursor-pointer">
                Schedule Follow-up
              </button>
              */}
              <button 
                onClick={onClose}
                className="w-full bg-surface-variant dark:bg-slate-800 text-on-surface dark:text-molten-text py-2 rounded-lg font-label-md text-label-md hover:bg-outline-variant transition-colors cursor-pointer text-center"
              >
                Close Drawer
              </button>
            </div>
          </>
        ) : (
          <div className="flex-grow flex items-center justify-center text-arctic-text-muted">
            Error loading call log data.
          </div>
        )}
      </div>
  );
};

export default CallTranscriptDrawer;
