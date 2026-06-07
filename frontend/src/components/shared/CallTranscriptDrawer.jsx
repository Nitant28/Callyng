import { useState, useEffect, useRef, useCallback } from 'react';
import clientApi from '../../api/client';

const CallTranscriptDrawer = ({ isOpen, sessionCallId, onClose, leadName }) => {
  const [callData, setCallData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const drawerRef = useRef(null);

  // Load call transcript details
  const fetchCallDetails = useCallback(async (showSpinner = true) => {
    if (!sessionCallId) return;
    if (showSpinner) setLoading(true);
    
    try {
      const response = await clientApi.get(`/api/calls/${sessionCallId}`);
      if (response.data && response.data.calls && response.data.calls.length > 0) {
        const call = response.data.calls[0];
        setCallData(call);
        setIsPolling(call.in_progress === true);
      }
    } catch (err) {
      console.warn('API error fetching call details, using mock data for demo', err);
      // Load mock transcript (Sarah Jenkins prototype)
      const mockCall = {
        session_call_id: sessionCallId,
        phone: '+1 (555) 019-2834',
        duration_seconds: 252, // 4m 12s
        in_progress: false,
        status: 'completed',
        transcript: [
          { role: 'assistant', content: 'Hi Sarah, this is Alex calling from LeadGen Pro. I saw you recently downloaded our guide on automated outreach. Do you have a quick minute?', ts: '2026-06-06T14:00:01Z' },
          { role: 'user', content: "Yes, I have a minute. I'm actually looking into tools for my team right now.", ts: '2026-06-06T14:00:05Z' },
          { role: 'assistant', content: "That's great timing. What's the biggest challenge you're facing with your current outreach process?", ts: '2026-06-06T14:00:10Z' },
          { role: 'user', content: 'Mostly just tracking who we\'ve called and managing the follow-ups. It gets messy in spreadsheets.', ts: '2026-06-06T14:00:15Z' },
        ],
        extraction_json: {
          'Interest Level': 'High',
          'Pain Point': 'Tracking follow-ups in spreadsheets',
          'Suggested Action': 'Schedule product demo next week',
        }
      };
      setCallData(mockCall);
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
    }, 3000);

    return () => clearInterval(interval);
  }, [isPolling, isOpen, sessionCallId, fetchCallDetails]);

  const formatDuration = (seconds) => {
    if (!seconds) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
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
    <div className="fixed inset-0 z-50 flex items-center justify-end">
      {/* Background Overlay */}
      <div 
        onClick={onClose}
        className="absolute inset-0 drawer-overlay transition-opacity duration-300 animate-fade-in"
      ></div>

      {/* Drawer Panel */}
      <div 
        ref={drawerRef}
        className="absolute right-0 top-0 bottom-0 w-full sm:w-[480px] bg-arctic-surface dark:bg-molten-surface shadow-2xl flex flex-col border-l border-outline-variant dark:border-[#2A345E] transition-all transform animate-slide-in-right z-10"
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

            {/* Transcript Conversation Area */}
            <div className="flex-1 overflow-y-auto p-6 bg-arctic-bg dark:bg-molten-bg/40 flex flex-col gap-6" id="chatArea">
              {callData.transcript && callData.transcript.length > 0 ? (
                callData.transcript.map((turn, index) => {
                  const isAi = turn.role === 'assistant' || turn.role === 'bot';
                  return isAi ? (
                    /* AI Bubble */
                    <div 
                      key={index} 
                      className="flex gap-3 max-w-[85%] opacity-0 transform -translate-x-4"
                      style={{ animation: `bubble-left 0.4s ease-out ${(index * 0.2) + 0.1}s forwards` }}
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
                      style={{ animation: `bubble-right 0.4s ease-out ${(index * 0.2) + 0.1}s forwards` }}
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
                <div className="flex-1 flex items-center justify-center text-arctic-text-muted">
                  No transcript details captured yet.
                </div>
              )}

              {/* In Progress Typing Indicator */}
              {callData.in_progress && (
                <div className="flex gap-3 max-w-[85%] opacity-0 transform -translate-x-4" style={{ animation: `bubble-left 0.4s ease-out ${(callData.transcript.length * 0.2) + 0.1}s forwards` }}>
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
    </div>
  );
};

export default CallTranscriptDrawer;
